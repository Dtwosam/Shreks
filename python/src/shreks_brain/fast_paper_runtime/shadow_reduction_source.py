from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from shreks_brain.paper import PaperPositionState
from shreks_brain.paper_validation import FastPaperCheckpointRecord

from .models import FastPaperRuntimeManifest
from .persisted_quotes import FastPaperShadowReductionRead
from .shadow_ledger import (
    FastPaperShadowLedgerBinding,
    load_latest_fast_paper_shadow_ledger_checkpoint,
)
from .shadow_runtime_state import (
    FastPaperShadowRuntimeState,
    load_latest_fast_paper_shadow_runtime_state,
)


FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_reduction_source"
)
FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_VERSION = 1

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "binding_fingerprint_sha256",
        "paper_checkpoint_sequence",
        "paper_checkpoint_payload_sha256",
        "shadow_runtime_state_fingerprint_sha256",
        "market_key",
        "position_id",
        "mint",
        "current_exposure_fraction_hex",
        "reduction_reads",
        "record_fingerprint_sha256",
    }
)
_READ_KEYS = frozenset(
    {
        "target_exposure_fraction_hex",
        "input_amount_raw",
    }
)
_MAX_U64 = 2**64 - 1


@dataclass(frozen=True, slots=True)
class FastPaperShadowReductionSourceRecord:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    binding_fingerprint_sha256: str
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    shadow_runtime_state_fingerprint_sha256: str
    market_key: str
    position_id: str
    mint: str
    current_exposure_fraction: float
    reduction_reads: tuple[FastPaperShadowReductionRead, ...]
    record_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_NAME:
            raise ValueError(
                "shadow reduction source schema_name is incompatible"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "shadow reduction source schema_version is incompatible"
            )
        for name in (
            "manifest_fingerprint_sha256",
            "binding_fingerprint_sha256",
            "paper_checkpoint_payload_sha256",
            "shadow_runtime_state_fingerprint_sha256",
            "record_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        _require_non_negative_int(
            "paper_checkpoint_sequence",
            self.paper_checkpoint_sequence,
        )
        for name in ("market_key", "position_id", "mint"):
            _require_text(name, getattr(self, name))
        _require_exposure(
            "current_exposure_fraction",
            self.current_exposure_fraction,
        )
        if (
            not isinstance(self.reduction_reads, tuple)
            or not all(
                type(value) is FastPaperShadowReductionRead
                for value in self.reduction_reads
            )
        ):
            raise ValueError(
                "reduction_reads must contain exact FastPaperShadowReductionRead values"
            )
        previous: float | None = None
        for value in self.reduction_reads:
            target = value.target_exposure_fraction
            if target >= self.current_exposure_fraction:
                raise ValueError(
                    "shadow reduction source target must be below current exposure"
                )
            if previous is not None and target <= previous:
                raise ValueError(
                    "shadow reduction source targets must be strictly increasing"
                )
            previous = target
        if _record_fingerprint(self) != self.record_fingerprint_sha256:
            raise ValueError(
                "shadow reduction source record fingerprint mismatch"
            )


def build_fast_paper_shadow_reduction_source_record(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    market_key: str,
    reduction_reads: tuple[FastPaperShadowReductionRead, ...],
) -> FastPaperShadowReductionSourceRecord:
    _require_exact_latest_pair(
        manifest,
        binding,
        paper_checkpoint,
        runtime_state,
    )
    _require_text("market_key", market_key)
    if (
        not isinstance(reduction_reads, tuple)
        or not all(
            type(value) is FastPaperShadowReductionRead
            for value in reduction_reads
        )
    ):
        raise ValueError(
            "reduction_reads must contain exact FastPaperShadowReductionRead values"
        )

    mapping = _market_mapping(runtime_state, market_key)
    _require_open_position(
        paper_checkpoint,
        position_id=mapping.position_id,
        mint=mapping.mint,
    )
    expected_targets = tuple(
        target
        for target in manifest.action_policy.reduce_target_exposure_candidates
        if target < mapping.current_exposure_fraction
    )
    actual_targets = tuple(
        value.target_exposure_fraction for value in reduction_reads
    )
    if actual_targets != expected_targets:
        raise ValueError(
            "shadow reduction source must cover the complete eligible action-policy target set"
        )

    values = {
        "schema_name": FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_REDUCTION_SOURCE_SCHEMA_VERSION,
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": paper_checkpoint.sequence,
        "paper_checkpoint_payload_sha256": paper_checkpoint.payload_sha256,
        "shadow_runtime_state_fingerprint_sha256": (
            runtime_state.state_fingerprint_sha256
        ),
        "market_key": mapping.market_key,
        "position_id": mapping.position_id,
        "mint": mapping.mint,
        "current_exposure_fraction": mapping.current_exposure_fraction,
        "reduction_reads": reduction_reads,
    }
    fingerprint = hashlib.sha256(
        _canonical_json(_document_values(values))
    ).hexdigest()
    return FastPaperShadowReductionSourceRecord(
        **values,
        record_fingerprint_sha256=fingerprint,
    )


def write_fast_paper_shadow_reduction_source_record(
    record: FastPaperShadowReductionSourceRecord,
    directory: str | Path,
) -> Path:
    if type(record) is not FastPaperShadowReductionSourceRecord:
        raise ValueError(
            "record must be exact FastPaperShadowReductionSourceRecord"
        )
    if _record_fingerprint(record) != record.record_fingerprint_sha256:
        raise ValueError(
            "shadow reduction source record fingerprint mismatch"
        )
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow reduction source directory must be an existing regular non-symlink directory"
        )
    destination = root / _record_filename(
        record.shadow_runtime_state_fingerprint_sha256,
        record.market_key,
    )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            "shadow reduction source record already exists"
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


def read_fast_paper_shadow_reduction_source_record(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    market_key: str,
    directory: str | Path,
) -> FastPaperShadowReductionSourceRecord:
    _require_exact_latest_pair(
        manifest,
        binding,
        paper_checkpoint,
        runtime_state,
    )
    _require_text("market_key", market_key)
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow reduction source directory must be an existing regular non-symlink directory"
        )
    path = root / _record_filename(
        runtime_state.state_fingerprint_sha256,
        market_key,
    )
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow reduction source record must be an existing regular non-symlink file"
        )
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise ValueError(
            "shadow reduction source record must have exactly one trailing newline"
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
            "shadow reduction source record is malformed JSON"
        ) from exc
    if type(document) is not dict or frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "shadow reduction source record has unknown or missing fields"
        )
    if _canonical_json(document) != raw:
        raise ValueError(
            "shadow reduction source record must use canonical JSON"
        )

    try:
        reduction_reads = _decode_reads(document["reduction_reads"])
        record = FastPaperShadowReductionSourceRecord(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            manifest_fingerprint_sha256=(
                document["manifest_fingerprint_sha256"]
            ),
            binding_fingerprint_sha256=(
                document["binding_fingerprint_sha256"]
            ),
            paper_checkpoint_sequence=document[
                "paper_checkpoint_sequence"
            ],
            paper_checkpoint_payload_sha256=document[
                "paper_checkpoint_payload_sha256"
            ],
            shadow_runtime_state_fingerprint_sha256=document[
                "shadow_runtime_state_fingerprint_sha256"
            ],
            market_key=document["market_key"],
            position_id=document["position_id"],
            mint=document["mint"],
            current_exposure_fraction=_decode_float_hex(
                "current_exposure_fraction_hex",
                document["current_exposure_fraction_hex"],
            ),
            reduction_reads=reduction_reads,
            record_fingerprint_sha256=document[
                "record_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"shadow reduction source record content is incompatible: {exc}"
        ) from exc

    expected = build_fast_paper_shadow_reduction_source_record(
        manifest,
        binding,
        paper_checkpoint,
        runtime_state,
        market_key,
        record.reduction_reads,
    )
    if record != expected:
        raise ValueError(
            "shadow reduction source record does not match current durable state"
        )
    return record


def _require_exact_latest_pair(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be exact FastPaperRuntimeManifest")
    if type(binding) is not FastPaperShadowLedgerBinding:
        raise ValueError(
            "binding must be exact FastPaperShadowLedgerBinding"
        )
    if type(paper_checkpoint) is not FastPaperCheckpointRecord:
        raise ValueError(
            "paper_checkpoint must be exact FastPaperCheckpointRecord"
        )
    if type(runtime_state) is not FastPaperShadowRuntimeState:
        raise ValueError(
            "runtime_state must be exact FastPaperShadowRuntimeState"
        )
    latest_checkpoint = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    if latest_checkpoint is None or latest_checkpoint != paper_checkpoint:
        raise ValueError(
            "shadow reduction source requires exact latest paper checkpoint"
        )
    latest_runtime = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    if latest_runtime is None or latest_runtime != runtime_state:
        raise ValueError(
            "shadow reduction source requires exact latest runtime state"
        )
    if (
        runtime_state.binding_fingerprint_sha256
        != binding.binding_fingerprint_sha256
    ):
        raise ValueError(
            "shadow reduction source runtime binding fingerprint mismatch"
        )
    if (
        runtime_state.paper_checkpoint_sequence != paper_checkpoint.sequence
        or runtime_state.paper_checkpoint_payload_sha256
        != paper_checkpoint.payload_sha256
    ):
        raise ValueError(
            "shadow reduction source checkpoint/runtime pair is torn"
        )


def _market_mapping(
    runtime_state: FastPaperShadowRuntimeState,
    market_key: str,
):
    matches = tuple(
        value
        for value in runtime_state.market_positions
        if value.market_key == market_key
    )
    if len(matches) != 1:
        raise ValueError(
            "shadow reduction source requires exactly one durable OPEN market mapping"
        )
    return matches[0]


def _require_open_position(
    paper_checkpoint: FastPaperCheckpointRecord,
    *,
    position_id: str,
    mint: str,
) -> None:
    matches = tuple(
        value
        for value in paper_checkpoint.state.ledger.positions
        if value.position_id == position_id
    )
    if len(matches) != 1:
        raise ValueError(
            "shadow reduction source durable position is missing or ambiguous"
        )
    position = matches[0]
    if position.state is not PaperPositionState.OPEN:
        raise ValueError(
            "shadow reduction source durable position must be OPEN"
        )
    if position.mint != mint:
        raise ValueError(
            "shadow reduction source durable position mint mismatch"
        )


def _record_filename(
    runtime_state_fingerprint_sha256: str,
    market_key: str,
) -> str:
    _require_sha256(
        "runtime_state_fingerprint_sha256",
        runtime_state_fingerprint_sha256,
    )
    _require_text("market_key", market_key)
    material = {
        "market_key": market_key,
        "runtime_state_fingerprint_sha256": (
            runtime_state_fingerprint_sha256
        ),
    }
    digest = hashlib.sha256(
        _canonical_json(material)
    ).hexdigest()
    return f"{digest}.json"


def _record_fingerprint(
    record: FastPaperShadowReductionSourceRecord,
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
                    "binding_fingerprint_sha256": (
                        record.binding_fingerprint_sha256
                    ),
                    "paper_checkpoint_sequence": (
                        record.paper_checkpoint_sequence
                    ),
                    "paper_checkpoint_payload_sha256": (
                        record.paper_checkpoint_payload_sha256
                    ),
                    "shadow_runtime_state_fingerprint_sha256": (
                        record.shadow_runtime_state_fingerprint_sha256
                    ),
                    "market_key": record.market_key,
                    "position_id": record.position_id,
                    "mint": record.mint,
                    "current_exposure_fraction": (
                        record.current_exposure_fraction
                    ),
                    "reduction_reads": record.reduction_reads,
                }
            )
        )
    ).hexdigest()


def _document(
    record: FastPaperShadowReductionSourceRecord,
) -> dict[str, object]:
    document = _document_values(
        {
            "schema_name": record.schema_name,
            "schema_version": record.schema_version,
            "manifest_fingerprint_sha256": (
                record.manifest_fingerprint_sha256
            ),
            "binding_fingerprint_sha256": (
                record.binding_fingerprint_sha256
            ),
            "paper_checkpoint_sequence": record.paper_checkpoint_sequence,
            "paper_checkpoint_payload_sha256": (
                record.paper_checkpoint_payload_sha256
            ),
            "shadow_runtime_state_fingerprint_sha256": (
                record.shadow_runtime_state_fingerprint_sha256
            ),
            "market_key": record.market_key,
            "position_id": record.position_id,
            "mint": record.mint,
            "current_exposure_fraction": (
                record.current_exposure_fraction
            ),
            "reduction_reads": record.reduction_reads,
        }
    )
    document["record_fingerprint_sha256"] = (
        record.record_fingerprint_sha256
    )
    return document


def _document_values(
    values: dict[str, object],
) -> dict[str, object]:
    reads = values["reduction_reads"]
    if (
        not isinstance(reads, tuple)
        or not all(
            type(value) is FastPaperShadowReductionRead
            for value in reads
        )
    ):
        raise ValueError(
            "shadow reduction source requires exact reduction reads"
        )
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "manifest_fingerprint_sha256": (
            values["manifest_fingerprint_sha256"]
        ),
        "binding_fingerprint_sha256": (
            values["binding_fingerprint_sha256"]
        ),
        "paper_checkpoint_sequence": values[
            "paper_checkpoint_sequence"
        ],
        "paper_checkpoint_payload_sha256": values[
            "paper_checkpoint_payload_sha256"
        ],
        "shadow_runtime_state_fingerprint_sha256": values[
            "shadow_runtime_state_fingerprint_sha256"
        ],
        "market_key": values["market_key"],
        "position_id": values["position_id"],
        "mint": values["mint"],
        "current_exposure_fraction_hex": _float_hex(
            values["current_exposure_fraction"]
        ),
        "reduction_reads": [
            {
                "target_exposure_fraction_hex": _float_hex(
                    value.target_exposure_fraction
                ),
                "input_amount_raw": str(value.input_amount_raw),
            }
            for value in reads
        ],
    }


def _decode_reads(
    raw: object,
) -> tuple[FastPaperShadowReductionRead, ...]:
    if not isinstance(raw, list):
        raise ValueError(
            "shadow reduction source reduction_reads must be a list"
        )
    values: list[FastPaperShadowReductionRead] = []
    for item in raw:
        if type(item) is not dict or frozenset(item) != _READ_KEYS:
            raise ValueError(
                "shadow reduction source reduction read has unknown or missing fields"
            )
        values.append(
            FastPaperShadowReductionRead(
                target_exposure_fraction=_decode_float_hex(
                    "target_exposure_fraction_hex",
                    item["target_exposure_fraction_hex"],
                ),
                input_amount_raw=_decode_u64_text(
                    "input_amount_raw",
                    item["input_amount_raw"],
                ),
            )
        )
    return tuple(values)


def _float_hex(value: object) -> str:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("shadow reduction source float must be finite")
    return float(value).hex()


def _decode_float_hex(name: str, value: object) -> float:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be hexadecimal float text")
    try:
        result = float.fromhex(value)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be hexadecimal float text"
        ) from exc
    if not math.isfinite(result) or result.hex() != value:
        raise ValueError(
            f"{name} must be canonical finite hexadecimal float text"
        )
    return result


def _decode_u64_text(name: str, value: object) -> int:
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not value.isdigit()
        or (value != "0" and value.startswith("0"))
    ):
        raise ValueError(f"{name} must be canonical u64 text")
    result = int(value)
    if not 0 <= result <= _MAX_U64 or str(result) != value:
        raise ValueError(f"{name} must be canonical u64 text")
    return result


def _require_exposure(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 < float(value) <= 1.0
    ):
        raise ValueError(
            f"{name} must be finite within (0,1]"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


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
    raise ValueError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
