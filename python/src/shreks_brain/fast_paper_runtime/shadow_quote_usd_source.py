from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from .codec import verify_fast_paper_runtime_bindings
from .models import FastPaperRuntimeManifest
from .shadow import FastPaperShadowDecisionEvidence
from .shadow_execution_input import FastPaperShadowQuoteUsdEvidence


FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_quote_usd_source"
)
FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_VERSION = 1

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "decision_evidence_fingerprint_sha256",
        "source_event_id",
        "market_key",
        "evaluated_at_unix_ms",
        "quote_mint",
        "quote_usd_evidence",
        "record_fingerprint_sha256",
    }
)
_USD_KEYS = frozenset(
    {
        "quote_mint",
        "observed_at_unix_ms",
        "quote_to_usd_rate_hex",
        "source_version",
        "source_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowQuoteUsdSourceRecord:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    decision_evidence_fingerprint_sha256: str
    source_event_id: str
    market_key: str
    evaluated_at_unix_ms: int
    quote_mint: str
    quote_usd_evidence: FastPaperShadowQuoteUsdEvidence
    record_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_NAME:
            raise ValueError(
                "shadow quote/USD source schema_name is incompatible"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "shadow quote/USD source schema_version is incompatible"
            )
        for name in (
            "manifest_fingerprint_sha256",
            "decision_evidence_fingerprint_sha256",
            "record_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        for name in ("source_event_id", "market_key", "quote_mint"):
            _require_text(name, getattr(self, name))
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )
        if type(self.quote_usd_evidence) is not FastPaperShadowQuoteUsdEvidence:
            raise ValueError(
                "quote_usd_evidence must be exact FastPaperShadowQuoteUsdEvidence"
            )
        if self.quote_usd_evidence.quote_mint != self.quote_mint:
            raise ValueError(
                "shadow quote/USD source quote mint mismatch"
            )
        if (
            self.quote_usd_evidence.observed_at_unix_ms
            > self.evaluated_at_unix_ms
        ):
            raise ValueError(
                "future quote/USD observation cannot bind shadow decision"
            )
        if _record_fingerprint(self) != self.record_fingerprint_sha256:
            raise ValueError(
                "shadow quote/USD source record fingerprint mismatch"
            )


def build_fast_paper_shadow_quote_usd_source_record(
    manifest: FastPaperRuntimeManifest,
    decision_evidence: FastPaperShadowDecisionEvidence,
    quote_usd_evidence: FastPaperShadowQuoteUsdEvidence,
) -> FastPaperShadowQuoteUsdSourceRecord:
    _require_decision_binding(manifest, decision_evidence)
    if type(quote_usd_evidence) is not FastPaperShadowQuoteUsdEvidence:
        raise ValueError(
            "quote_usd_evidence must be exact FastPaperShadowQuoteUsdEvidence"
        )

    expected_quote_mint = decision_evidence.entry_quote.quote_mint
    if expected_quote_mint != manifest.quote_mint:
        raise ValueError(
            "shadow quote/USD decision quote mint does not match runtime manifest"
        )
    if quote_usd_evidence.quote_mint != expected_quote_mint:
        raise ValueError(
            "shadow quote/USD evidence quote mint does not match decision evidence"
        )
    if (
        quote_usd_evidence.observed_at_unix_ms
        > decision_evidence.evaluated_at_unix_ms
    ):
        raise ValueError(
            "future quote/USD observation cannot authorize shadow decision"
        )

    values = {
        "schema_name": FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_VERSION,
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "decision_evidence_fingerprint_sha256": (
            decision_evidence.evidence_fingerprint_sha256
        ),
        "source_event_id": decision_evidence.source_event_id,
        "market_key": decision_evidence.market_key,
        "evaluated_at_unix_ms": decision_evidence.evaluated_at_unix_ms,
        "quote_mint": expected_quote_mint,
        "quote_usd_evidence": quote_usd_evidence,
    }
    fingerprint = hashlib.sha256(
        _canonical_json(_document_values(values))
    ).hexdigest()
    return FastPaperShadowQuoteUsdSourceRecord(
        **values,
        record_fingerprint_sha256=fingerprint,
    )


def write_fast_paper_shadow_quote_usd_source_record(
    record: FastPaperShadowQuoteUsdSourceRecord,
    directory: str | Path,
) -> Path:
    if type(record) is not FastPaperShadowQuoteUsdSourceRecord:
        raise ValueError(
            "record must be exact FastPaperShadowQuoteUsdSourceRecord"
        )
    if _record_fingerprint(record) != record.record_fingerprint_sha256:
        raise ValueError(
            "shadow quote/USD source record fingerprint mismatch"
        )

    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow quote/USD source directory must be an existing regular non-symlink directory"
        )
    root = root.resolve(strict=True)
    destination = root / _record_filename(
        record.decision_evidence_fingerprint_sha256
    )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            "shadow quote/USD source record already exists"
        )

    payload = _canonical_json(_document(record)) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-",
        dir=root,
    )
    temporary = Path(temporary_name)
    published = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination, follow_symlinks=False)
        published = True
        os.chmod(destination, 0o600)
        _fsync_directory(root)
        temporary.unlink()
        _fsync_directory(root)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        if published:
            destination.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        raise
    return destination


def read_fast_paper_shadow_quote_usd_source_record(
    manifest: FastPaperRuntimeManifest,
    decision_evidence: FastPaperShadowDecisionEvidence,
    directory: str | Path,
) -> FastPaperShadowQuoteUsdSourceRecord:
    _require_decision_binding(manifest, decision_evidence)
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow quote/USD source directory must be an existing regular non-symlink directory"
        )
    root = root.resolve(strict=True)
    path = root / _record_filename(
        decision_evidence.evidence_fingerprint_sha256
    )
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow quote/USD source record must be an existing regular non-symlink file"
        )
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise ValueError(
            "shadow quote/USD source record must have exactly one trailing newline"
        )
    raw = payload[:-1]
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            "shadow quote/USD source record is malformed JSON"
        ) from exc
    if type(document) is not dict or frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "shadow quote/USD source record has unknown or missing fields"
        )
    if _canonical_json(document) != raw:
        raise ValueError(
            "shadow quote/USD source record must use canonical JSON"
        )

    try:
        usd = _decode_quote_usd(document["quote_usd_evidence"])
        record = FastPaperShadowQuoteUsdSourceRecord(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            manifest_fingerprint_sha256=document[
                "manifest_fingerprint_sha256"
            ],
            decision_evidence_fingerprint_sha256=document[
                "decision_evidence_fingerprint_sha256"
            ],
            source_event_id=document["source_event_id"],
            market_key=document["market_key"],
            evaluated_at_unix_ms=document["evaluated_at_unix_ms"],
            quote_mint=document["quote_mint"],
            quote_usd_evidence=usd,
            record_fingerprint_sha256=document[
                "record_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"shadow quote/USD source record content is incompatible: {exc}"
        ) from exc

    expected = build_fast_paper_shadow_quote_usd_source_record(
        manifest,
        decision_evidence,
        record.quote_usd_evidence,
    )
    if record != expected:
        raise ValueError(
            "shadow quote/USD source record does not match current decision authority"
        )
    return record


def _require_decision_binding(
    manifest: FastPaperRuntimeManifest,
    decision_evidence: FastPaperShadowDecisionEvidence,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be exact FastPaperRuntimeManifest")
    if type(decision_evidence) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "decision_evidence must be exact FastPaperShadowDecisionEvidence"
        )
    verify_fast_paper_runtime_bindings(manifest)
    if decision_evidence.release_source_sha != manifest.release_source_sha:
        raise ValueError(
            "shadow quote/USD decision release source does not match runtime manifest"
        )
    if (
        decision_evidence.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "shadow quote/USD decision manifest fingerprint mismatch"
        )
    if decision_evidence.champion_version != manifest.champion_version:
        raise ValueError(
            "shadow quote/USD decision champion version mismatch"
        )
    if (
        decision_evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "shadow quote/USD decision champion fingerprint mismatch"
        )
    if (
        decision_evidence.action_policy_version
        != manifest.action_policy.version
    ):
        raise ValueError(
            "shadow quote/USD decision action policy version mismatch"
        )


def _record_filename(
    decision_evidence_fingerprint_sha256: str,
) -> str:
    _require_sha256(
        "decision_evidence_fingerprint_sha256",
        decision_evidence_fingerprint_sha256,
    )
    return f"{decision_evidence_fingerprint_sha256}.json"


def _record_fingerprint(
    record: FastPaperShadowQuoteUsdSourceRecord,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            _document_values(
                {
                    "schema_name": record.schema_name,
                    "schema_version": record.schema_version,
                    "manifest_fingerprint_sha256": (
                        record.manifest_fingerprint_sha256
                    ),
                    "decision_evidence_fingerprint_sha256": (
                        record.decision_evidence_fingerprint_sha256
                    ),
                    "source_event_id": record.source_event_id,
                    "market_key": record.market_key,
                    "evaluated_at_unix_ms": (
                        record.evaluated_at_unix_ms
                    ),
                    "quote_mint": record.quote_mint,
                    "quote_usd_evidence": record.quote_usd_evidence,
                }
            )
        )
    ).hexdigest()


def _document(
    record: FastPaperShadowQuoteUsdSourceRecord,
) -> dict[str, object]:
    result = _document_values(
        {
            "schema_name": record.schema_name,
            "schema_version": record.schema_version,
            "manifest_fingerprint_sha256": (
                record.manifest_fingerprint_sha256
            ),
            "decision_evidence_fingerprint_sha256": (
                record.decision_evidence_fingerprint_sha256
            ),
            "source_event_id": record.source_event_id,
            "market_key": record.market_key,
            "evaluated_at_unix_ms": record.evaluated_at_unix_ms,
            "quote_mint": record.quote_mint,
            "quote_usd_evidence": record.quote_usd_evidence,
        }
    )
    result["record_fingerprint_sha256"] = (
        record.record_fingerprint_sha256
    )
    return result


def _document_values(
    values: dict[str, object],
) -> dict[str, object]:
    usd = values["quote_usd_evidence"]
    if type(usd) is not FastPaperShadowQuoteUsdEvidence:
        raise ValueError(
            "shadow quote/USD source requires exact quote/USD evidence"
        )
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "manifest_fingerprint_sha256": (
            values["manifest_fingerprint_sha256"]
        ),
        "decision_evidence_fingerprint_sha256": (
            values["decision_evidence_fingerprint_sha256"]
        ),
        "source_event_id": values["source_event_id"],
        "market_key": values["market_key"],
        "evaluated_at_unix_ms": values["evaluated_at_unix_ms"],
        "quote_mint": values["quote_mint"],
        "quote_usd_evidence": _encode_quote_usd(usd),
    }


def _encode_quote_usd(
    value: FastPaperShadowQuoteUsdEvidence,
) -> dict[str, object]:
    return {
        "quote_mint": value.quote_mint,
        "observed_at_unix_ms": value.observed_at_unix_ms,
        "quote_to_usd_rate_hex": value.quote_to_usd_rate.hex(),
        "source_version": value.source_version,
        "source_fingerprint_sha256": (
            value.source_fingerprint_sha256
        ),
    }


def _decode_quote_usd(
    value: object,
) -> FastPaperShadowQuoteUsdEvidence:
    if type(value) is not dict or frozenset(value) != _USD_KEYS:
        raise ValueError(
            "shadow quote/USD evidence has unknown or missing fields"
        )
    rate = _decode_positive_float_hex(
        "quote_to_usd_rate_hex",
        value["quote_to_usd_rate_hex"],
    )
    return FastPaperShadowQuoteUsdEvidence(
        quote_mint=value["quote_mint"],
        observed_at_unix_ms=value["observed_at_unix_ms"],
        quote_to_usd_rate=rate,
        source_version=value["source_version"],
        source_fingerprint_sha256=value[
            "source_fingerprint_sha256"
        ],
    )


def _decode_positive_float_hex(
    name: str,
    value: object,
) -> float:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be canonical float hex")
    try:
        result = float.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be canonical float hex") from exc
    if (
        not math.isfinite(result)
        or result <= 0.0
        or result.hex() != value
    ):
        raise ValueError(f"{name} must be canonical positive float hex")
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_sha256(name: str, value: object) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
